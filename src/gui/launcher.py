import sys
import streamlit.web.cli as stcli

def main():
    sys.argv = ["streamlit", "run", "src/gui/app.py"]
    sys.exit(stcli.main())