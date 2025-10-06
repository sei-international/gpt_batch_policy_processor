#!/bin/bash

# Azure Web App startup script for Streamlit application
# This script configures and starts the Streamlit server

# Create .jobs directory if it doesn't exist
mkdir -p .jobs

# Set Streamlit configuration
export STREAMLIT_SERVER_PORT=8000
export STREAMLIT_SERVER_ADDRESS=0.0.0.0
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_SERVER_ENABLE_CORS=false
export STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true

# Start Streamlit
python -m streamlit run main.py \
    --server.port=8000 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=true
