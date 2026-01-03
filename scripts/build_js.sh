#!/bin/bash
set -e
cd js
npm install
npm run build

mkdir -p ../python/orion_finance_sdk_py/js_sdk
cp dist/bundle.js ../python/orion_finance_sdk_py/js_sdk/
cp node_modules/node-tfhe/tfhe_bg.wasm ../python/orion_finance_sdk_py/js_sdk/
cp node_modules/node-tkms/kms_lib_bg.wasm ../python/orion_finance_sdk_py/js_sdk/
