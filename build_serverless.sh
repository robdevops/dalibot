#!/bin/bash
set -euo pipefail

ME=${0##*/}
MYDIR=$(realpath $(dirname $0))

parse_args() {
	PLATFORM=""
	PY_VERSION=""
	while getopts ":hp:v:" opt; do
		case $opt in
		  p  ) PLATFORM=$OPTARG ;;
		  v  ) PY_VERSION=$OPTARG ;;
		  :  ) echo "Option -$OPTARG requires an argument." && exit 3 ;;
		  \? ) echo "Invalid option: -$OPTARG" && exit 3 ;;
		  h  ) usage ;;
		esac
	done
[[ -n $PLATFORM ]] || usage
if [[ -n $PY_VERSION && ! $PY_VERSION =~ ^3\.[0-9]+$ ]]; then
    echo "Invalid Python version: $PY_VERSION (expected e.g. 3.13)"
    exit 3
fi
if [[ $PLATFORM == 'arm64' ]]; then
    pip_platform="manylinux2014_aarch64"
elif [[ $PLATFORM == 'x86_64' ]]; then
    pip_platform="manylinux2014_x86_64"
else
    usage
fi
}

usage() {
	echo "Usage: $ME -p <arm64|x86_64> [-v <python version, e.g. 3.13>]"
	echo "-v is the Python runtime of your cloud function. Defaults to the Python running this script."
	exit 3
}

parse_args $@
mkdir -p ${MYDIR}/staging
cd ${MYDIR}/staging
rm -vrf Pillow* pillow* PIL
pip_args=(--platform $pip_platform --only-binary=:all:)
if [[ -n $PY_VERSION ]]; then
    pip_args+=(--python-version $PY_VERSION --implementation cp)
fi
pip3 install "${pip_args[@]}" pillow --upgrade --target=${MYDIR}/staging/

[[ -s bot.py ]] || ln -vs ../bot.py bot.py
[[ -s lib ]] || ln -vs ../lib lib

if [[ -f dalibot.ini ]]; then
    zip -r dalibot_${PLATFORM}.zip . && echo -e "\ndalibot_${PLATFORM}.zip created."
else
    if [[ -f ../dalibot.ini ]]; then
        cp -v ../dalibot.ini dalibot.ini
    else
        cp -v ../dalibot.ini.template dalibot.ini
    fi
fi

echo "If you still need to edit the config, do so and then update the package:"
echo "cd ${MYDIR}/staging"
echo "Edit dalibot.ini"
echo "zip dalibot_${PLATFORM}.zip dalibot.ini"
echo "See ${MYDIR}/doc/serverless.md for help"
