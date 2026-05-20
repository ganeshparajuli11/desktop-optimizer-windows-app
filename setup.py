from setuptools import setup, find_packages

setup(
    name="sysctl-monitor",
    version="3.0.0",
    author="ganes",
    description="Windows System Control Center - GPU, RAM, Disk, Network, Docker monitor",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourname/sysctl",
    py_modules=["sysctl"],
    install_requires=[
        "customtkinter>=5.2.0",
        "psutil>=5.9.0",
        "pynvml>=11.5.0",
    ],
    entry_points={
        "console_scripts": [
            "sysctl=sysctl:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Topic :: System :: Monitoring",
    ],
)
