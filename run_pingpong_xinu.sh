#!/bin/sh
# PingPong.abcl を Xinu (arm-qemu) 上で動かす一連の手順。
#  1. abcl2c に --xinu を付けて C を生成
#  2. Xinu の apps/abcl_pingpong.c に配置
#  3. Xinu kernel をビルド (arm-none-eabi-gcc)
#  4. QEMU で起動し、シリアル出力を表示
set -e
cd "$(dirname "$0")"

XINU=/Users/kodamay/projects/xinu-raz/xinu
COMPILER_ROOT=/opt/homebrew/bin/arm-none-eabi-

# 1. translator
dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/PingPong.abcl \
    -o /tmp/pp_xinu.c --xinu --max-msgs 12

# 2. place into Xinu apps
cp /tmp/pp_xinu.c "$XINU/apps/abcl_pingpong.c"

# 3. build Xinu (apps/Makerules には abcl_pingpong.c を追加済み、
#    system/main.c には aipl_main の起動コードを追加済み)
( cd "$XINU/compile" && \
  make PLATFORM=arm-qemu COMPILER_ROOT=$COMPILER_ROOT >/tmp/xinu_build.log 2>&1 )

# 4. run under QEMU; シリアルをファイルへリダイレクト
rm -f /tmp/xinu_out.txt
qemu-system-arm -M versatilepb -cpu arm1176 -m 256M \
    -kernel "$XINU/compile/xinu.elf" \
    -no-reboot -display none -serial file:/tmp/xinu_out.txt &
QPID=$!
sleep 10
kill -9 $QPID 2>/dev/null
wait 2>/dev/null

echo "=== Xinu serial output ==="
tr -d '\r' </tmp/xinu_out.txt
