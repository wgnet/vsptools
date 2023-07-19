import setuptools
import os.path

# The directory containing this file
HERE = os.path.abspath(os.path.dirname(__file__))

# The text of the README file
with open(os.path.join(HERE, "README.md")) as fid:
    README = fid.read()

with open(os.path.join(HERE, "requirements.txt")) as fid:
    requirements = fid.read().split()

setuptools.setup(
    name="vsp-versioner",
    version="0.6.3",
    description="Tool for getting version number for git repository suitable for game development process.",
    long_description=README,
    long_description_content_type="text/markdown",
    license="",
    python_requires=">=3.8",
    packages=['versioner'],
    zip_safe=False,
    maintainer="",
    maintainer_email="",
    url="",
    entry_points={"console_scripts": ["versioner=versioner.__main__:main"]},
    install_requires=requirements
)
