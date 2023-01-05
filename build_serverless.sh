#!/bin/bash
set -euo pipefail

mkdir -p staging
cd staging
pip3 install requests pillow --upgrade --target=$(pwd)

[[ -s bot.py ]] || ln -vs ../bot.py bot.py
[[ -s lib ]] || ln -vs ../lib lib
if ! [[ -f dalibot.ini ]] && ! [[ ../dalibot.ini ]]; then
    cp -v ../dalibot.ini.example dalibot.ini
elif ! [[ -f dalibot.ini ]] && [[ -f ../dalibot.ini ]]; then
    cp -v ../dalibot.ini dalibot.ini
fi

echo
echo "Complete the setup with:"
echo cd staging
echo edit dalibot.ini
echo zip -r script.zip .
echo see doc/serverless.md for help
