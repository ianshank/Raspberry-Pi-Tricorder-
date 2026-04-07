from setuptools import setup, find_packages

setup(
    name="tricorder-neural",
    version="1.0.0",
    description="Neural network-enhanced sensor fusion platform on Raspberry Pi 5",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "pydantic>=2.9.0",
        "pyyaml>=6.0.0",
        "fastapi>=0.115.0",
        "uvicorn>=0.32.0",
        "websockets>=12.0",
        "numpy>=1.26.0",
        "structlog>=24.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.24.0",
            "pytest-cov>=5.0.0",
            "pytest-mock>=3.14.0",
            "httpx>=0.27.0",
            "ruff>=0.8.0",
            "mypy>=1.13.0",
        ],
        "agent": [
            "langchain>=0.3.0",
            "langgraph>=0.2.0",
        ],
        "hardware": [
            "smbus2>=0.4.0",
            "spidev>=3.6",
            "pyserial>=3.5",
            "RPi.GPIO>=0.7.0",
        ],
        "hailo": [
            "hailort>=4.17",
        ],
    },
    entry_points={
        "console_scripts": [
            "tricorder-mcp=mcp_server.server:main",
            "tricorder-agent=agents.langgraph_agent:main",
        ],
    },
)
