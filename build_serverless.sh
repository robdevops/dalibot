#!/bin/bash
set -euo pipefail

ME=${0##*/}
MYDIR=${0%/*}

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
	echo "Usage: $ME -p <arm64|x86_64>"
	exit 3
}


parse_args $@
mkdir -p ${MYDIR}/staging
cd ${MYDIR}/staging
rm -vrf Pillow*
pip3 install --platform $pip_platform --only-binary=:all: requests pillow --upgrade --target=$(pwd)

[[ -s bot.py ]] || ln -vs ../bot.py bot.py
[[ -s lib ]] || ln -vs ../lib lib

if [[ dalibot.ini ]]; then
    zip -r dalibot_${PLATFORM}.zip .
else
    if ! [[ -f dalibot.ini ]] && ! [[ ../dalibot.ini ]]; then
        cp -v ../dalibot.ini.example dalibot.ini
    elif ! [[ -f dalibot.ini ]] && [[ -f ../dalibot.ini ]]; then
        cp -v ../dalibot.ini dalibot.ini
    fi
fi

echo
echo "If you still need to edit dalibot.ini, do so and then update the package:"
echo "cd staging"
echo "Edit dalibot.ini"
echo "zip dalibot_${PLATFORM}.zip dalibot.ini"
echo "See doc/serverless.md for help"
