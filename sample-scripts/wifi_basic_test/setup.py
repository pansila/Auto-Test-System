import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="WiFi Basic Test",
    version="0.1.0",
    author="Robotest Co.,Ltd",
    author_email="author@robotest.com",
    description="A Test Package To Run Tests For A WiFi device",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pypa/sampleproject",
    packages=setuptools.find_packages('src'),
    package_dir={'':'src'},   # tell distutils packages are under src
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    package_data={
        '': ['scripts/*.md', 'scripts/*.robot'],   # robotframework test scripts should under scripts
    },
    install_requires=[
        'robotest_utilities>=0.1.1',
    ],
)