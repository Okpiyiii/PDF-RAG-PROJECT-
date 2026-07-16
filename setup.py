from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pdf-rag-pipeline",
    version="1.0.0",
    author="PDF RAG Pipeline Contributors",
    description="Structured PDF extraction engine for RAG pipelines — bounding boxes, tables, OCR, and accessibility tagging",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/pdf-rag-pipeline",
    packages=find_packages(include=["pdf_rag_pipeline", "pdf_rag_pipeline.*"]),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "PyMuPDF>=1.23.0",
        "pdfplumber>=0.10.0",
        "Pillow>=10.0.0",
        "pytesseract>=0.3.10",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov",
            "black",
            "ruff",
            "mypy",
        ],
    },
    entry_points={
        "console_scripts": [
            "pdf-rag=pdf_rag_pipeline.cli:main",
        ],
    },
)
