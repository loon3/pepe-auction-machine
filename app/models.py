from datetime import datetime
from app import db

class Auction(db.Model):
    __tablename__ = 'auctions'
    
    id = db.Column(db.Integer, primary_key=True)
    asset_name = db.Column(db.String(255), nullable=False)
    asset_qty = db.Column(db.Float, nullable=False)  # Float to support divisible assets (up to 8 decimals)
    utxo_txid = db.Column(db.String(64), nullable=False)
    utxo_vout = db.Column(db.Integer, nullable=False)
    start_block = db.Column(db.Integer, nullable=False)
    end_block = db.Column(db.Integer, nullable=False)
    start_price_sats = db.Column(db.BigInteger, nullable=False)
    end_price_sats = db.Column(db.BigInteger, nullable=False)
    price_decrement = db.Column(db.BigInteger, nullable=False)
    blocks_after_end = db.Column(db.Integer, nullable=False, default=144)
    status = db.Column(db.String(20), nullable=False, default='upcoming')  # upcoming, active, sold, closed, finished, expired
    spent_txid = db.Column(db.String(64), nullable=True)  # Transaction that spent the UTXO (context determined by status)
    spent_block = db.Column(db.Integer, nullable=True)  # Block height when UTXO was spent
    spent_at = db.Column(db.DateTime, nullable=True)  # Timestamp when UTXO was spent (transaction blocktime)
    recipient = db.Column(db.String(64), nullable=True)  # Recipient address (first non-OP_RETURN output of spending tx)
    seller = db.Column(db.String(64), nullable=True)  # Seller address (from PSBT input or UTXO)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship to PSBTs
    psbts = db.relationship('PSBT', backref='auction', lazy=True, cascade='all, delete-orphan')
    
    # Note: No unique constraint on UTXO to allow creating new auctions after expiration
    # Uniqueness is enforced in application code for active/relevant auctions only
    
    def to_dict(self, include_psbts=False):
        """Convert auction to dictionary for API responses"""
        data = {
            'id': self.id,
            'asset_name': self.asset_name,
            'asset_qty': self.asset_qty,
            'utxo_txid': self.utxo_txid,
            'utxo_vout': self.utxo_vout,
            'start_block': self.start_block,
            'end_block': self.end_block,
            'start_price_sats': self.start_price_sats,
            'end_price_sats': self.end_price_sats,
            'price_decrement': self.price_decrement,
            'blocks_after_end': self.blocks_after_end,
            'status': self.status,
            'spent_txid': self.spent_txid,
            'spent_block': self.spent_block,
            'spent_at': self.spent_at.isoformat() if self.spent_at else None,
            'recipient': self.recipient,
            'seller': self.seller,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        if include_psbts:
            data['psbts'] = [psbt.to_dict() for psbt in self.psbts]
        
        return data
    
    def get_utxo_string(self):
        """Return UTXO in txid:vout format"""
        return f"{self.utxo_txid}:{self.utxo_vout}"
    
    def __repr__(self):
        return f'<Auction {self.id}: {self.asset_name} ({self.status})>'


class PSBT(db.Model):
    __tablename__ = 'psbts'
    
    id = db.Column(db.Integer, primary_key=True)
    auction_id = db.Column(db.Integer, db.ForeignKey('auctions.id'), nullable=False)
    block_number = db.Column(db.Integer, nullable=False)
    price_sats = db.Column(db.BigInteger, nullable=False)
    psbt_data = db.Column(db.Text, nullable=False)
    
    # Add unique constraint on auction_id and block_number
    __table_args__ = (
        db.UniqueConstraint('auction_id', 'block_number', name='unique_auction_block'),
    )
    
    def to_dict(self):
        """Convert PSBT to dictionary for API responses"""
        return {
            'id': self.id,
            'auction_id': self.auction_id,
            'block_number': self.block_number,
            'price_sats': self.price_sats,
            'psbt_data': self.psbt_data
        }
    
    def __repr__(self):
        return f'<PSBT {self.id}: Block {self.block_number}, Price {self.price_sats}>'

