from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).resolve().parent
VERSION = "5.389"


def read_text(filename: str) -> str:
    return (ROOT / filename).read_text(encoding="utf-8")


def read_requirements(filename: str) -> list[str]:
    requirements = []
    for raw_line in read_text(filename).splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            requirements.append(line)
    return requirements


setup(
    name="AutoMindCloud",
    version=VERSION,
    description=(
        "Industrial engineering, scientific-computing, and technical-visualization "
        "tools for Google Colab"
    ),
    long_description=read_text("README.md"),
    long_description_content_type="text/markdown",
    author="Artemio Araya Day",
    author_email="artemioaday@gmail.com",
    maintainer="AutoMind Ltda.",
    license="AutoMind Limited Use License 1.0 (Proprietary)",
    license_files=["LICENSE"],
    python_requires=">=3.8",
    install_requires=read_requirements("requirements.txt"),
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "AutoMindCloud": ["*.png", "*.mp3"],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Mathematics",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=(
        "industrial engineering scientific computing google colab CAD URDF USD DXF "
        "symbolic mathematics technical visualization"
    ),
)
