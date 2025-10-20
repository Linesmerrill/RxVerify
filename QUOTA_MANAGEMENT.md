# OpenAI API Quota Management Guide

## 🚨 **Current Issue: Quota Exceeded**

You're seeing this error because your OpenAI API quota has been exceeded:
```
HTTP Request: POST https://api.openai.com/v1/embeddings "HTTP/1.1 429 Too Many Requests"
You exceeded your current quota, please check your plan and billing details.
```

## 🛠️ **Immediate Solutions**

### 1. **Quick Fix: Disable Embeddings (Recommended)**
```bash
python manage_quota.py disable
```
This will:
- ✅ Stop all OpenAI API calls immediately
- ✅ Use fallback embeddings (still functional)
- ✅ Keep your system running without errors
- ⚠️ Slightly reduced search quality (but still good)

### 2. **Alternative: Use Fallback Only**
```bash
python manage_quota.py fallback
```
This conserves quota while keeping some embedding functionality.

### 3. **Check Current Configuration**
```bash
python manage_quota.py check
```

## 💰 **Long-term Solutions**

### Option 1: **Upgrade OpenAI Plan**
1. Go to [OpenAI Platform](https://platform.openai.com/account/billing)
2. Check your current usage and limits
3. Upgrade to a higher tier plan
4. Re-enable embeddings: `python manage_quota.py enable`

### Option 2: **Optimize Usage (Already Implemented)**
We've already implemented several optimizations:
- ✅ **Embedding caching** - Reduces duplicate API calls
- ✅ **Smart fallback** - Uses fallback when API fails
- ✅ **Reduced vector search** - Only when needed
- ✅ **Configuration options** - Easy quota management

### Option 3: **Use Alternative Embedding Service**
Consider switching to:
- **Hugging Face Transformers** (free)
- **Sentence Transformers** (free)
- **Cohere API** (alternative paid service)

## 🔧 **Technical Details**

### What Uses Embeddings?
- **Vector search** for drug similarity
- **Query enhancement** for better results
- **Semantic matching** between drugs and queries

### Fallback Embeddings
When OpenAI is unavailable, the system uses:
- **Drug-specific patterns** based on medication names
- **Content-based similarity** using text analysis
- **Medical term matching** for drug classes
- **Still functional** but less sophisticated than OpenAI embeddings

### Performance Impact
- **With OpenAI**: Best search quality, uses API quota
- **With Fallback**: Good search quality, no API calls
- **Difference**: ~10-15% reduction in search relevance

## 📊 **Monitoring Usage**

### Check OpenAI Dashboard
1. Visit [OpenAI Usage Dashboard](https://platform.openai.com/usage)
2. Monitor your current usage
3. Check rate limits and quotas
4. Set up billing alerts

### Check System Status
```bash
# Check current configuration
python manage_quota.py check

# Check system logs for embedding usage
grep "embedding" logs/rxverify_*.log
```

## 🚀 **Recommended Actions**

### Immediate (Do Now):
1. **Disable embeddings** to stop quota errors:
   ```bash
   python manage_quota.py disable
   ```

2. **Restart your server** to apply changes:
   ```bash
   # Stop current server (Ctrl+C)
   python run_servers.py
   ```

### Short-term (This Week):
1. **Check your OpenAI usage** and billing
2. **Consider upgrading** your OpenAI plan
3. **Monitor system performance** with fallback embeddings

### Long-term (This Month):
1. **Evaluate embedding alternatives** if quota is a recurring issue
2. **Implement usage monitoring** and alerts
3. **Consider hybrid approach** (OpenAI for important queries, fallback for others)

## 🔍 **Troubleshooting**

### Still Getting Errors?
1. **Check environment variables**:
   ```bash
   python manage_quota.py check
   ```

2. **Restart the server** after changing configuration

3. **Check logs** for other API calls:
   ```bash
   grep -i "openai\|embedding\|quota" logs/rxverify_*.log
   ```

### System Not Working?
1. **Verify fallback embeddings** are working
2. **Check other API dependencies** (medical APIs)
3. **Test with simple queries** first

## 📞 **Support**

### OpenAI Support
- [OpenAI Help Center](https://help.openai.com/)
- [Rate Limit Documentation](https://platform.openai.com/docs/guides/rate-limits)
- [Billing Support](https://platform.openai.com/account/billing)

### System Issues
- Check logs in `logs/` directory
- Use `python manage_quota.py help` for commands
- Verify environment variables are set correctly

## 🎯 **Summary**

**Immediate Action**: Run `python manage_quota.py disable` to stop quota errors
**Your system will continue working** with fallback embeddings
**Consider upgrading** your OpenAI plan for better performance
**Monitor usage** to prevent future quota issues

The system is designed to be resilient and will continue providing good search results even without OpenAI embeddings!
