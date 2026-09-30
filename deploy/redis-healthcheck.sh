#!/bin/sh
# redis-cli 的密码仅经环境传入，不出现在 argv，探测输出被抑制。
REDISCLI_AUTH="$(cat /run/secrets/redis_probe)"
export REDISCLI_AUTH
result="$(redis-cli --user probe ping 2>/dev/null)"
test "$result" = PONG
