import os
import sys
from pathlib import Path


def main():
    os.system(
        f"{sys.executable} -m streamlit run {Path(__file__).parent / 'app.py'}"
    )


if __name__ == '__main__':
    main()
