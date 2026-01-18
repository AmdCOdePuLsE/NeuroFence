from setuptools import setup, find_packages

setup(
    name="neurofence-sdk",
    version="1.0.0",
    description="NeuroFence - AI agent safety system with contamination detection and isolation",
    packages=find_packages(include=["neurofence_sdk", "neurofence_sdk.*"]),
    install_requires=[
        "requests>=2.28",
    ],
    python_requires=">=3.9",
)
