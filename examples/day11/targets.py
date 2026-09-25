"""後端必須明選；模擬器不通不改連正式專案。"""
from pathlib import Path
from store import SQLiteTestStore

def open_store(config):
    mode=config['backend']
    if mode=='memory-control':
        from memory_control import MemoryControlStore
        return MemoryControlStore()
    if mode=='sqlite-test':return SQLiteTestStore(config['db'])
    if mode not in ('emulator','cloud'):raise ValueError('未知 backend。')
    from firestore_store import FirestoreStore
    return FirestoreStore(config['project'],config['namespace'],cloud=mode=='cloud',
                          approve_cloud=config.get('approve_cloud') is True)
