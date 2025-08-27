#!/bin/bash
# Remove compressed output to prevent extraction to temp directory
rm -f /home/site/wwwroot/output.tar.gz
# Start the application
cd /home/site/wwwroot && python -m streamlit run main.py --server.port=8000 --server.address=0.0.0.0