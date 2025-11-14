# shopify-bulk-scripts

Shopify bulk upload scripts for managing products from various brands (Nike, Adidas, Jordan, etc.)

## Setup

### 1. Configure Sensitive Parameters

**IMPORTANT:** Before running any scripts, you must set up your credentials:

1. Copy the example parameters file:
   ```bash
   cp parameters.example.py parameters.py
   ```

2. Edit `parameters.py` and add your actual Shopify credentials:
   - `SHOPIFY_STORE`: Your Shopify store URL (e.g., "yourstore.myshopify.com")
   - `ACCESS_TOKEN`: Your Shopify Admin API access token
   - `API_VERSION`: The Shopify API version (default: "2025-07")

3. **Never commit `parameters.py` to git!** This file is already excluded in `.gitignore`

### 2. Install Dependencies

```bash
pip install beautifulsoup4 requests demjson3
```

### 3. Test Your Configuration

Before running any bulk upload scripts, test your setup:

```bash
cd test-script
python3 test-connection.py
```

This will verify that:
- Your `parameters.py` is configured correctly
- Your Shopify credentials are valid
- The API connection is working
- You have proper permissions

If the test passes, you're ready to use all the other scripts!

## Project Structure

```
.
├── parameters.py                  # Your credentials (NOT in git)
├── parameters.example.py          # Template file (safe to commit)
├── test-script/                   # Test connection script
├── bulk-upload-shopify/          # Main bulk upload scripts
├── bulk-upload-adidas-men-clothing/
├── bulk-upload-adidas-men-shoes/
├── bulk-upload-adidas-women-clothing/
├── bulk-upload-adidas-women-shoes/
├── bulk-upload-jordan/
├── bulk-upload-nike-men/
└── bulk-upload-nike-women/
```

## Usage

Each folder contains a script for uploading specific brand/category products to Shopify. All scripts automatically import credentials from `parameters.py`.

Example:
```bash
cd bulk-upload-nike-men
python bulk-upload-shopify-nike-men.py
```

## Security Notes

- **Never push `parameters.py` to any public repository**
- Keep your `ACCESS_TOKEN` secure and rotate it regularly
- Review `.gitignore` to ensure sensitive files are excluded
