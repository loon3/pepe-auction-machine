#!/usr/bin/env python3
"""
Migration script to remove unique constraint on utxo_txid/utxo_vout
This allows creating new auctions for expired UTXOs while keeping historical records
"""
import sqlite3
import os
import shutil
from datetime import datetime

# Database path
DB_PATH = './data/auctions.db'
BACKUP_PATH = f'./data/auctions_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

def migrate():
    """Remove unique constraint from auctions table"""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return False
    
    # Create backup
    print(f"📦 Creating backup at {BACKUP_PATH}")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"✓ Backup created")
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("\n🔧 Starting migration...")
        
        # Check if unique constraint exists
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='auctions'")
        current_schema = cursor.fetchone()[0]
        
        if 'UNIQUE' not in current_schema:
            print("✓ No unique constraint found - database already migrated")
            conn.close()
            return True
        
        print("📝 Current schema has unique constraint")
        
        # Create new table without unique constraint
        cursor.execute("""
            CREATE TABLE auctions_new (
                id INTEGER PRIMARY KEY,
                asset_name VARCHAR(255) NOT NULL,
                asset_qty INTEGER NOT NULL,
                utxo_txid VARCHAR(64) NOT NULL,
                utxo_vout INTEGER NOT NULL,
                start_block INTEGER NOT NULL,
                end_block INTEGER NOT NULL,
                start_price_sats BIGINT NOT NULL,
                end_price_sats BIGINT NOT NULL,
                price_decrement BIGINT NOT NULL,
                blocks_after_end INTEGER NOT NULL DEFAULT 144,
                status VARCHAR(20) NOT NULL DEFAULT 'upcoming',
                purchase_txid VARCHAR(64),
                closed_txid VARCHAR(64),
                created_at DATETIME NOT NULL
            )
        """)
        print("✓ Created new table without unique constraint")
        
        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO auctions_new 
            SELECT * FROM auctions
        """)
        rows_copied = cursor.rowcount
        print(f"✓ Copied {rows_copied} auction records")
        
        # Drop old table
        cursor.execute("DROP TABLE auctions")
        print("✓ Dropped old table")
        
        # Rename new table
        cursor.execute("ALTER TABLE auctions_new RENAME TO auctions")
        print("✓ Renamed new table to auctions")
        
        # Commit changes
        conn.commit()
        print("\n✅ Migration completed successfully!")
        print(f"   - Removed unique constraint on (utxo_txid, utxo_vout)")
        print(f"   - {rows_copied} auction records preserved")
        print(f"   - Backup saved at {BACKUP_PATH}")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {str(e)}")
        print(f"   Database restored from backup at {BACKUP_PATH}")
        return False
        
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 70)
    print("AUCTION DATABASE MIGRATION")
    print("Removing unique constraint to allow auction history")
    print("=" * 70)
    
    success = migrate()
    
    if success:
        print("\n🎉 You can now create new auctions for expired UTXOs!")
        print("   Historical auction records are preserved in the database.")
    else:
        print("\n⚠️  Migration failed. Please check the error and try again.")
        print("   Your original database is backed up.")
    
    print("\n" + "=" * 70)

