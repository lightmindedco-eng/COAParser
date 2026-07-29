@echo off
title COA Parser Test - Delta Symbol and Filename Issues
echo ========================================================================
echo Testing COA Parser for Known Issues:      
echo 1. (g).txt filename extraction 
echo 2. Delta-9 THC detection with Greek Δ symbol
echo ========================================================================

python batch_process.py "C:\Users\kimep\Documents\GitHub\OpenCode\COAParser\data" "Output" /v >> test_parser_errors.log 2>&1

if exist test_parser_errors.log (
    echo Test complete. Check Output/(g).txt and search for Delta-9 in results
    
REM Search output files with correct Δ symbol handling:  
(type "C:\Users\kimep\Documents\GitHub\OpenCode\COAParser\Output\*(Delta*|Liquid Loud*" /r | findstr/i/n "^delta" 2>nul)

if not errorlevel^1 echo SUCCESS: Delta THC detected!
if errorlevel^1 (echo MISSING: Check for parsing issues)

REM Filename verification:  
(type "C:\Users\kimep\Documents\GitHub\xpenCode\CABParser\data'\1A40E*.pd" /r | findstr/i/n "^gold drop") if not errorlevel  ^ echo SUCCESS: Gold Drop filename extracted!)
echo ========================================================================)
