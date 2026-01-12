# Database Setup Guide

Quick reference for setting up the PostgreSQL database for email-monitor.

**Context**: You are logged in as root inside the PostgreSQL LXC container (192.168.1.228)

## Step 1: Run the Schema Script

The schema file is located at `/root/schema.sql`.

Run the schema as postgres superuser:
```bash
su - postgres -c "psql -f /root/schema.sql"
```

Or switch to postgres user and run interactively:
```bash
su - postgres
psql -f /root/schema.sql
```

## Step 2: Set Secure Passwords

Switch to postgres user:
```bash
su - postgres
psql -d email_auto_reply
```

Then in psql:
```sql
-- Set passwords (use actual passwords from Ansible vault)
ALTER USER readonly WITH PASSWORD 'your_readonly_password';
ALTER USER readwrite WITH PASSWORD 'your_readwrite_password';

-- Exit
\q
```

Or as one-liner from root:
```bash
su - postgres -c "psql -d email_auto_reply -c \"ALTER USER readonly WITH PASSWORD 'your_readonly_password';\""
su - postgres -c "psql -d email_auto_reply -c \"ALTER USER readwrite WITH PASSWORD 'your_readwrite_password';\""
```

## Step 3: Verify Setup

```bash
# Check tables were created
su - postgres -c "psql -d email_auto_reply -c '\dt'"

# Check users
su - postgres -c "psql -d email_auto_reply -c '\du'"

# Check filter rules
su - postgres -c "psql -d email_auto_reply -c 'SELECT * FROM email_filter_rules;'"

# Check views
su - postgres -c "psql -d email_auto_reply -c '\dv'"
```

## Step 4: Verify pg_hba.conf Configuration

Check that the email-auto-reply LXC (192.168.1.238) can connect:
```bash
cat /etc/postgresql/15/main/pg_hba.conf | grep email_auto_reply
```

Should have entries like:
```
host    email_auto_reply    readwrite     192.168.1.0/24    md5
host    email_auto_reply    readonly      192.168.1.0/24    md5
```

If missing, add them:
```bash
echo "host    email_auto_reply    readwrite     192.168.1.0/24    md5" >> /etc/postgresql/15/main/pg_hba.conf
echo "host    email_auto_reply    readonly      192.168.1.0/24    md5" >> /etc/postgresql/15/main/pg_hba.conf

# Reload PostgreSQL
systemctl reload postgresql
```

## Step 5: Test Connection from Email-Auto-Reply LXC

From another terminal, SSH to the email-auto-reply LXC (192.168.1.238):
```bash
ssh root@192.168.1.238
```

Then test connection:
```bash
# Install psql client if needed
apt-get update && apt-get install -y postgresql-client

# Test readonly user
psql -h 192.168.1.228 -U readonly -d email_auto_reply -c "SELECT COUNT(*) FROM processed_emails;"

# Test readwrite user (this is what the service uses)
psql -h 192.168.1.228 -U readwrite -d email_auto_reply -c "SELECT COUNT(*) FROM processed_emails;"
```

## Troubleshooting

### Connection Refused from Email-Auto-Reply LXC

If the email-auto-reply service can't connect:

1. **Check PostgreSQL is listening on all interfaces**:
```bash
cat /etc/postgresql/15/main/postgresql.conf | grep listen_addresses
```

Should be:
```
listen_addresses = '*'
```

If not, update it:
```bash
sed -i "s/^#*listen_addresses.*/listen_addresses = '*'/" /etc/postgresql/15/main/postgresql.conf
systemctl restart postgresql
```

2. **Check firewall** (if any):
```bash
# Check if firewall is active
systemctl status ufw

# If active, allow PostgreSQL
ufw allow from 192.168.1.0/24 to any port 5432
```

3. **Verify PostgreSQL is running**:
```bash
systemctl status postgresql
netstat -tlnp | grep 5432
```

### Password Authentication Failed

Make sure the passwords match what's in Ansible vault:
- Check vault: `ansible-vault view ~/home-server-related/ansible/vault/secrets.yml`
- Variable: `ALGO_TRADING_DB_PASSWORD_RW`

## Quick Commands (as postgres user)

```bash
# Switch to postgres user
su - postgres

# Connect to database
psql -d email_auto_reply
```

Then in psql:
```sql
-- View recent emails
SELECT * FROM recent_activity;

-- View pending emails
SELECT * FROM pending_emails;

-- View active filter rules
SELECT * FROM filter_rules_active;

-- Add a blacklist rule
INSERT INTO email_filter_rules (rule_type, pattern, description)
VALUES ('blacklist_sender', 'noreply@', 'Block all no-reply addresses');

-- View email statistics
SELECT status, COUNT(*) as count, MAX(processed_at) as last_processed
FROM processed_emails
GROUP BY status;

-- Check database size
SELECT pg_size_pretty(pg_database_size('email_auto_reply'));

-- List all tables with row counts
SELECT schemaname,relname,n_live_tup 
FROM pg_stat_user_tables 
ORDER BY n_live_tup DESC;
```

## Backup Commands

```bash
# Backup the database
su - postgres -c "pg_dump email_auto_reply | gzip > /root/email_auto_reply_backup_$(date +%Y%m%d).sql.gz"

# Restore from backup
su - postgres -c "gunzip -c /root/email_auto_reply_backup_20260111.sql.gz | psql email_auto_reply"
```
