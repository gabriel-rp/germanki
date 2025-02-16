import os
import sys
from pathlib import Path


def main():
    os.system(
        f'cd {Path(__file__).parent} && {sys.executable} -m streamlit run app.py --server.headless=false'
    )


if __name__ == '__main__':
    main()
