#!/usr/bin/env bash
set -e

# Configure postgresql.conf
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/16/main/postgresql.conf
sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/16/main/postgresql.conf

# Configure pg_hba.conf to trust local/WSL/Windows connections
cat << 'EOF' > /etc/postgresql/16/main/pg_hba.conf
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
host    all             all             0.0.0.0/0               trust
host    all             all             all                     trust
EOF

service postgresql restart

# Configure Redis
sed -i "s/^bind 127.0.0.1.*/bind 0.0.0.0/" /etc/redis/redis.conf
sed -i "s/^protected-mode yes/protected-mode no/" /etc/redis/redis.conf
service redis-server restart

echo "Services reconfigured and restarted successfully"
