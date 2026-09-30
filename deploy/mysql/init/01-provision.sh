# 由 MySQL 官方 entrypoint source；此文件保持不可执行，以复用安全客户端函数。
# probe 与领域账号先于健康探测就绪；仅空卷运行，不回显 SQL/凭据。
docker_process_sql < /run/secrets/mysql_bootstrap
