#!/bin/bash

# Version Update Script for RxVerify
# Generates a new version with timestamp and updates files

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Generate new version with current timestamp in UTC
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
NEW_VERSION="v1.0.0-beta.${TIMESTAMP}"

echo -e "${BLUE}🔄 Updating version to: ${NEW_VERSION}${NC}"

# Update VERSION file
echo "${NEW_VERSION}" > VERSION
echo -e "${GREEN}✅ Updated VERSION file${NC}"

# Update frontend/index.html with the new version
if [ -f "frontend/index.html" ]; then
    # Replace {{VERSION}} placeholder with actual version
    sed -i.bak "s/{{VERSION}}/${NEW_VERSION}/g" frontend/index.html
    rm frontend/index.html.bak 2>/dev/null || true
    echo -e "${GREEN}✅ Updated frontend/index.html${NC}"
else
    echo "⚠️  frontend/index.html not found, skipping..."
fi

# Update cache-busting version in frontend/index.html
CACHE_VERSION=$(date +%s)
sed -i.bak "s/app\.js?v=[0-9]*/app.js?v=${CACHE_VERSION}/g" frontend/index.html
rm frontend/index.html.bak 2>/dev/null || true
echo -e "${GREEN}✅ Updated cache-busting version to v=${CACHE_VERSION}${NC}"

# Auto-commit and push changes
echo -e "${BLUE}📝 Committing version changes...${NC}"

# Add the modified files
git add VERSION frontend/index.html

# Commit with descriptive message
git commit -m "Auto-update version to ${NEW_VERSION}

- Updated VERSION file to ${NEW_VERSION}
- Updated frontend cache-busting version to v=${CACHE_VERSION}
- Automated version update via update_version.sh"

# Push to remote repository
echo -e "${BLUE}🚀 Pushing changes to remote repository...${NC}"
git push

echo -e "${GREEN}🎉 Version update completed and pushed!${NC}"
echo -e "${BLUE}New version: ${NEW_VERSION}${NC}"
echo -e "${BLUE}Cache version: v=${CACHE_VERSION}${NC}"
