#!/bin/bash
set -euo pipefail

parse_args() {
	while getopts ":h:p:" opt; do
        PLATFORM=""
		case $opt in
		  p  ) PLATFORM=$OPTARG ;;
		  :  ) echo "Option -$OPTARG requires an argument." && exit 3 ;;
		  \? ) echo "Invalid option: -$OPTARG" && exit 3 ;;
		  h  ) usage ;;
		esac
	done
[[ -v PLATFORM ]] || usage
if [[ $PLATFORM == 'arm64' ]]; then
    pip_platform="manylinux2014_aarch64"
elif [[ $PLATFORM == 'x86_64' ]]; then
    pip_platform="manylinux1_x86_64"
else
    usage
fi
}


usage() {
	echo "Usage: ${0##*/} -p <arm64|x86_64>"
	exit 3
}


parse_args $@
mkdir -p staging
cd staging
rm -vrf Pillow*
pip3 install --platform $pip_platform --only-binary=:all: requests pillow --upgrade --target=$(pwd)

[[ -s bot.py ]] || ln -vs ../bot.py bot.py
[[ -s lib ]] || ln -vs ../lib lib
if ! [[ -f dalibot.ini ]] && ! [[ ../dalibot.ini ]]; then
    cp -v ../dalibot.ini.example dalibot.ini
elif ! [[ -f dalibot.ini ]] && [[ -f ../dalibot.ini ]]; then
    cp -v ../dalibot.ini dalibot.ini
fi

echo
echo "Complete the setup with:"
echo "cd staging"
echo "edit dalibot.ini"
echo "zip -r dalibot_${PLATFORM}.zip ."
echo "see doc/serverless.md for help"
