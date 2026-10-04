# 只读取公开字段，不执行dotenv内容；调用者提供task_env。
setting() {
  awk -v key="$1" -v fallback="$2" '
    $0 ~ "^[ \t]*(export[ \t]+)?" key "[ \t]*=" {
      count++; sub(/^[^=]*=[ \t]*/, ""); sub(/[ \t]+#.*/, ""); sub(/[ \t\r]+$/, "")
      if ($0 ~ /^"[^"]*"$/ || $0 ~ /^\047[^\047]*\047$/) $0=substr($0,2,length($0)-2)
      value=$0
    }
    END { if (count>1) exit 2; print count ? value : fallback }
  ' "$task_env"
}
