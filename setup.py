from setuptools import setup, find_packages

setup(
    name="neurofence-sdk",
    version="1.0.1",
    description="NeuroFence - AI agent safety system with contamination detection and isolation",
    packages=find_packages(include=["neurofence_sdk", "neurofence_sdk.*"]),
    install_requires=[
        "requests>=2.28",
    ],
    entry_points={
        "console_scripts": [
            "neurofence=neurofence_sdk.cli:main",
        ]
    },
    python_requires=">=3.9",
)
