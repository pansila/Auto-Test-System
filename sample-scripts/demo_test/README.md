# A Test Package Demonstrates How To Run A Test

### All tests in our platform are written in markdown, more specifically in the tables of markdown. You can put the test document along side the test tables. This way we can bind test scripts and test document together in a way both legible by humans and executable by the test runner.

### For more details about how to write a test, please refer to the demo test script after getting it installed. You can find it in the `Edit Test` page for the script content.

## Test Package
A test package is an `egg` format of python package that includes robotframework test scripts and corresponding test libraries. We can build such a package like building a normal python egg package with some extra requirements.
1. All test scripts should be put in the `scripts`.
2. A special robotframework test script `setup.robot` should be included in the `scripts` directory. It does some dirt work to set up the helper keywords and import necessary libraries.
3. scripts should be specified as data resources so that they can be packaged along with python files.

Here is an example of `setup.py`

```python
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Demo Test",
    version="0.0.1",
    author="Robotest Co.,Ltd",
    author_email="author@robotest.com",
    description="A test package demonstrates how to run a test",
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
        'robotest-builtin>=0.0.1',
    ],
)
```

## How It Works
Robotframework doesn't support test scripts of markdown format, we add a markdown parser to the robot so that it can extract test scripts from the tables that the first colum of the header row starts with the robot keywords such as `Settings`, `Variables`, `Test Cases` and so on. Any other tables and text will be ignored.

## Test Package Store
You can download test packages written by others from our `Test Store` page and reuse the test libraries of them so that you don't need to reinvent the wheel for similar test tasks.

You can also publish your test packages to others, be them free or charged. Just upload them on the `Test Store` page. Be noted that, you can keep your test packages proprietary if you don't want them go public. Just by tick the `Proprietary` checkbox in the top right corner before you uploading your package, then the test package is only seen by your team members if you upload it in a role of team, or could be seen by all your organization members if you upload it in a role of organization. If you don't tick the `Proprietary` checkbox, the test package will be seen by all users. You can change the package visibility scope anytime in your test package page if you are the package owner or the organization owner or the team owner.

## Where A Test Package Is Installed
A test package is installed under the user's directory on the server, you can find them on the `Edit Test` page.

## How To Make A Test Package
Just as what we will do for an `egg` python package, set up the scripts and python files, run the build command `python setup.py bdist_egg`.

Here is the directory structure of a test package.
```bash
$ ls
LICENSE  README.md  setup.py  src/
$ ls src
demo_test
$ ls src/demo_test
demotest.py  scripts/
$ ls src/demo_test/scripts/
demo-test.md  setup.robot
```