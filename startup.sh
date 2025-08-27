#!/bin/bash
# Remove compressed output to prevent extraction to temp directory
rm -f /home/site/wwwroot/output.tar.gz
# Remove any existing manifest to force running from /home/site/wwwroot
rm -f /home/site/wwwroot/oryx-manifest.toml
# Start the application
cd /home/site/wwwroot && python -m streamlit run main.py --server.port=8000 --server.address=0.0.0.0