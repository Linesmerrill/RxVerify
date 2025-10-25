"""
Drug Rating Service

This service handles drug rating and voting functionality, including
upvoting/downvoting drugs and managing hidden drugs based on ratings.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.drug_database_schema import DrugVote, DrugRating, VoteType, DrugStatus
from app.drug_database_manager import drug_db_manager

logger = logging.getLogger(__name__)


class DrugRatingService:
    """Handles drug rating and voting operations."""
    
    def __init__(self):
        self.hide_threshold = -0.5  # Hide drugs with rating <= -0.5
        self.min_votes_for_hiding = 3  # Need at least 3 votes to hide
    
    def _generate_user_id(self, ip_address: Optional[str], user_agent: Optional[str]) -> str:
        """Generate a consistent user ID for anonymous voting."""
        import hashlib
        
        # Create a hash from IP and user agent for anonymous identification
        identifier = f"{ip_address or 'unknown'}:{user_agent or 'unknown'}"
        return hashlib.md5(identifier.encode()).hexdigest()
    
    async def vote_on_drug(self, drug_id: str, vote_type: VoteType, 
                          user_id: Optional[str] = None, reason: Optional[str] = None,
                          ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> bool:
        """
        Vote on a drug (upvote or downvote).
        
        Args:
            drug_id: ID of the drug to vote on
            vote_type: Type of vote (upvote or downvote)
            user_id: Optional user ID (for authenticated users)
            reason: Optional reason for the vote
            ip_address: IP address for anonymous voting
            user_agent: User agent for anonymous voting
        
        Returns:
            bool: True if vote was recorded successfully
        """
        try:
            # Generate user ID for anonymous voting if not provided
            if not user_id:
                user_id = self._generate_user_id(ip_address, user_agent)
            
            # Check if drug exists
            drug = await drug_db_manager.get_drug_by_id(drug_id)
            if not drug:
                logger.warning(f"Cannot vote on non-existent drug: {drug_id}")
                return False
            
            # Check for duplicate votes (by user_id or ip_address) - only same vote type
            if await self._has_user_voted_with_type(drug_id, vote_type, user_id, ip_address):
                logger.warning(f"User has already voted {vote_type.value} on drug {drug_id}")
                return False
            
            # Create vote record
            vote_id = str(uuid.uuid4())
            vote = DrugVote(
                vote_id=vote_id,
                drug_id=drug_id,
                user_id=user_id,
                vote_type=vote_type,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Store vote
            await drug_db_manager.votes_collection.insert_one(vote.dict())
            
            # Update drug rating
            await self._update_drug_rating(drug_id, vote_type)
            
            # Check if drug should be hidden
            await self._check_and_hide_drug(drug_id)
            
            logger.info(f"Vote recorded: {vote_type} for drug {drug_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to vote on drug {drug_id}: {str(e)}")
            return False
    
    async def unvote_drug(self, drug_id: str, vote_type: VoteType, 
                         ip_address: Optional[str] = None, 
                         user_agent: Optional[str] = None) -> bool:
        """Remove a vote from a drug."""
        try:
            # Generate user ID for anonymous voting
            user_id = self._generate_user_id(ip_address, user_agent)
            
            # Check if user has voted on this drug with the specific vote type
            if not await self._has_user_voted_with_type(drug_id, vote_type, user_id, ip_address):
                logger.warning(f"User {user_id} tried to unvote {vote_type.value} on {drug_id} but hasn't voted with that type")
                return False
            
            # Remove the vote from database (only the specific vote type)
            query = {
                "drug_id": drug_id,
                "vote_type": vote_type.value
            }
            
            # Use the same logic as _has_user_voted for consistency
            if user_id and ip_address:
                query["$or"] = [
                    {"user_id": user_id},
                    {"ip_address": ip_address}
                ]
            elif user_id:
                query["user_id"] = user_id
            elif ip_address:
                query["ip_address"] = ip_address
            
            result = await drug_db_manager.votes_collection.delete_one(query)
            
            if result.deleted_count > 0:
                # Update drug rating (decrement the vote)
                await self._update_drug_rating(drug_id, vote_type, is_increment=False)
                logger.info(f"Successfully removed {vote_type.value} vote for drug {drug_id}")
                return True
            else:
                logger.warning(f"No vote found to remove for drug {drug_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to unvote on drug {drug_id}: {str(e)}")
            return False
    
    async def _has_user_voted_with_type(self, drug_id: str, vote_type: VoteType, 
                                       user_id: Optional[str], ip_address: Optional[str]) -> bool:
        """Check if user has voted on this drug with a specific vote type."""
        try:
            query = {
                "drug_id": drug_id,
                "vote_type": vote_type.value
            }
            
            # Check for votes by either user_id or ip_address
            if user_id and ip_address:
                query["$or"] = [
                    {"user_id": user_id},
                    {"ip_address": ip_address}
                ]
            elif user_id:
                query["user_id"] = user_id
            elif ip_address:
                query["ip_address"] = ip_address
            else:
                return False  # No way to identify user
            
            existing_vote = await drug_db_manager.votes_collection.find_one(query)
            return existing_vote is not None
            
        except Exception as e:
            logger.error(f"Failed to check existing votes with type: {str(e)}")
            return False
    
    async def _has_user_voted(self, drug_id: str, user_id: Optional[str], 
                             ip_address: Optional[str]) -> bool:
        """Check if user has already voted on this drug."""
        try:
            query = {"drug_id": drug_id}
            
            # Check for votes by either user_id or ip_address
            if user_id and ip_address:
                query["$or"] = [
                    {"user_id": user_id},
                    {"ip_address": ip_address}
                ]
            elif user_id:
                query["user_id"] = user_id
            elif ip_address:
                query["ip_address"] = ip_address
            else:
                return False  # No way to identify user
            
            existing_vote = await drug_db_manager.votes_collection.find_one(query)
            return existing_vote is not None
            
        except Exception as e:
            logger.error(f"Failed to check existing votes: {str(e)}")
            return False
    
    async def _update_drug_rating(self, drug_id: str, vote_type: VoteType, is_increment: bool = True):
        """Update the drug's rating statistics."""
        try:
            # Get current vote counts
            upvotes = await drug_db_manager.votes_collection.count_documents({
                "drug_id": drug_id,
                "vote_type": VoteType.UPVOTE
            })
            
            downvotes = await drug_db_manager.votes_collection.count_documents({
                "drug_id": drug_id,
                "vote_type": VoteType.DOWNVOTE
            })
            
            total_votes = upvotes + downvotes
            
            # Calculate rating score
            if total_votes > 0:
                rating_score = (upvotes - downvotes) / total_votes
            else:
                rating_score = 0.0
            
            # Update drug document
            await drug_db_manager.drugs_collection.update_one(
                {"drug_id": drug_id},
                {
                    "$set": {
                        "upvotes": upvotes,
                        "downvotes": downvotes,
                        "total_votes": total_votes,
                        "rating_score": rating_score,
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            logger.debug(f"Updated rating for drug {drug_id}: {upvotes} upvotes, {downvotes} downvotes, score: {rating_score}")
            
        except Exception as e:
            logger.error(f"Failed to update drug rating for {drug_id}: {str(e)}")
    
    async def _check_and_hide_drug(self, drug_id: str):
        """Check if drug should be hidden based on rating threshold."""
        try:
            drug = await drug_db_manager.get_drug_by_id(drug_id)
            if not drug:
                return
            
            # Check if drug meets hiding criteria
            should_hide = (
                drug.rating_score <= self.hide_threshold and 
                drug.total_votes >= self.min_votes_for_hiding
            )
            
            if should_hide and drug.status != DrugStatus.HIDDEN:
                # Hide the drug
                await drug_db_manager.drugs_collection.update_one(
                    {"drug_id": drug_id},
                    {
                        "$set": {
                            "status": DrugStatus.HIDDEN,
                            "last_updated": datetime.utcnow()
                        }
                    }
                )
                
                logger.info(f"Drug {drug_id} hidden due to poor rating: {drug.rating_score}")
            
            elif not should_hide and drug.status == DrugStatus.HIDDEN:
                # Unhide the drug if rating improved
                await drug_db_manager.drugs_collection.update_one(
                    {"drug_id": drug_id},
                    {
                        "$set": {
                            "status": DrugStatus.ACTIVE,
                            "last_updated": datetime.utcnow()
                        }
                    }
                )
                
                logger.info(f"Drug {drug_id} unhidden due to improved rating: {drug.rating_score}")
                
        except Exception as e:
            logger.error(f"Failed to check hiding status for drug {drug_id}: {str(e)}")
    
    async def get_drug_rating(self, drug_id: str) -> Optional[DrugRating]:
        """Get rating information for a specific drug."""
        try:
            drug = await drug_db_manager.get_drug_by_id(drug_id)
            if not drug:
                return None
            
            return DrugRating(
                drug_id=drug_id,
                total_votes=drug.total_votes,
                upvotes=drug.upvotes,
                downvotes=drug.downvotes,
                rating_score=drug.rating_score,
                is_hidden=drug.status == DrugStatus.HIDDEN,
                last_updated=drug.last_updated
            )
            
        except Exception as e:
            logger.error(f"Failed to get rating for drug {drug_id}: {str(e)}")
            return None
    
    async def get_hidden_drugs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of hidden drugs for admin review."""
        try:
            pipeline = [
                {"$match": {"status": DrugStatus.HIDDEN}},
                {
                    "$project": {
                        "drug_id": 1,
                        "name": 1,
                        "rating_score": 1,
                        "total_votes": 1,
                        "upvotes": 1,
                        "downvotes": 1,
                        "last_updated": 1
                    }
                },
                {"$sort": {"rating_score": 1, "total_votes": -1}},
                {"$limit": limit}
            ]
            
            cursor = drug_db_manager.drugs_collection.aggregate(pipeline)
            hidden_drugs = []
            
            async for doc in cursor:
                hidden_drugs.append({
                    "drug_id": doc["drug_id"],
                    "name": doc["name"],
                    "rating_score": doc["rating_score"],
                    "total_votes": doc["total_votes"],
                    "upvotes": doc["upvotes"],
                    "downvotes": doc["downvotes"],
                    "last_updated": doc["last_updated"]
                })
            
            return hidden_drugs
            
        except Exception as e:
            logger.error(f"Failed to get hidden drugs: {str(e)}")
            return []
    
    async def unhide_drug(self, drug_id: str, admin_reason: str) -> bool:
        """Manually unhide a drug (admin function)."""
        try:
            result = await drug_db_manager.drugs_collection.update_one(
                {"drug_id": drug_id},
                {
                    "$set": {
                        "status": DrugStatus.ACTIVE,
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Drug {drug_id} manually unhidden by admin: {admin_reason}")
                return True
            else:
                logger.warning(f"Failed to unhide drug {drug_id} - not found")
                return False
                
        except Exception as e:
            logger.error(f"Failed to unhide drug {drug_id}: {str(e)}")
            return False
    
    async def get_rating_stats(self) -> Dict[str, Any]:
        """Get overall rating statistics."""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": None,
                        "total_drugs": {"$sum": 1},
                        "active_drugs": {"$sum": {"$cond": [{"$eq": ["$status", DrugStatus.ACTIVE]}, 1, 0]}},
                        "hidden_drugs": {"$sum": {"$cond": [{"$eq": ["$status", DrugStatus.HIDDEN]}, 1, 0]}},
                        "total_votes": {"$sum": "$total_votes"},
                        "total_upvotes": {"$sum": "$upvotes"},
                        "total_downvotes": {"$sum": "$downvotes"},
                        "avg_rating": {"$avg": "$rating_score"}
                    }
                }
            ]
            
            cursor = drug_db_manager.drugs_collection.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            
            if result:
                stats = result[0]
                return {
                    "total_drugs": stats["total_drugs"],
                    "active_drugs": stats["active_drugs"],
                    "hidden_drugs": stats["hidden_drugs"],
                    "total_votes": stats["total_votes"],
                    "total_upvotes": stats["total_upvotes"],
                    "total_downvotes": stats["total_downvotes"],
                    "average_rating": round(stats["avg_rating"], 3) if stats["avg_rating"] else 0.0,
                    "hide_threshold": self.hide_threshold,
                    "min_votes_for_hiding": self.min_votes_for_hiding
                }
            else:
                return {
                    "total_drugs": 0,
                    "active_drugs": 0,
                    "hidden_drugs": 0,
                    "total_votes": 0,
                    "total_upvotes": 0,
                    "total_downvotes": 0,
                    "average_rating": 0.0,
                    "hide_threshold": self.hide_threshold,
                    "min_votes_for_hiding": self.min_votes_for_hiding
                }
                
        except Exception as e:
            logger.error(f"Failed to get rating stats: {str(e)}")
            return {}


# Global instance
drug_rating_service = DrugRatingService()
