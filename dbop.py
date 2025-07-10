'''Database content inspect and manual modification'''

import sqlite3

dbcon = sqlite3.connect("chatbot.db")
dbcon.execute("drop table resource_cache")
for table in ["chat_sessions", "messages", "research_cache"]:
    dbcon.execute(f"delete from {table}")
    print(table, dbcon.execute(f"select * from {table}").fetchall())
dbcon.commit()