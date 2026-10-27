from setuptools import find_packages, setup

setup(
    name="ingenii-annotate-backend",
    version="0.1.0",
    description="Multi-model annotation platform API (YOLOv26, Florence, DINO, SAM2, Gemini agent)",
    python_requires=">=3.11",
    packages=find_packages(include=["app", "app.*"]),
)
