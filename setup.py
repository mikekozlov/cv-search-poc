from setuptools import setup, find_packages
setup(
    name="cvsearch",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "click>=8.1.7",
        "python-dotenv>=1.0.1",
        "pydantic>=2.8.2",
        "pydantic-settings>=2.0.0",
        "openai>=1.42.0,<2",
        "faiss-cpu",
        "sentence-transformers",
        "streamlit",
        "python-pptx"
    ],
)