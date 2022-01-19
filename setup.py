#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup


setup(
    license="MIT",
    version="0.1.0",
    name="testinspect",

    python_requires=">=3.8",
    install_requires=[
        "pytest>=5.0", 
        "radon==5.1.0",
        "coverage>=5.0",
        "psutil==5.8.0"
    ],
    
    author="Owain Parry",
    author_email="oparry1@sheffield.ac.uk",

    py_modules=["testinspect"],
    entry_points={"pytest11": ["testinspect=testinspect"]}
)
