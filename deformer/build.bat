@echo off
del /f /q dist
pip install build
py -m build
