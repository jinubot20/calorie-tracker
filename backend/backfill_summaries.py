import database
import ai_engine
from sqlalchemy.orm import Session
from itertools import groupby
import logging

# Setup basic logging to see progress
logging.basicConfig(level=logging.INFO)

def backfill_summaries():
    db = database.SessionLocal()
    try:
        # 1. Get all users
        users = db.query(database.User).all()
        logging.info(f"Starting backfill for {len(users)} users.")

        for user in users:
            logging.info(f"Processing user: {user.name} ({user.email})")
            
            # 2. Get all meals for this user, sorted by date
            meals = sorted(user.meals, key=lambda x: x.timestamp.date())
            
            # 3. Group by date
            for date, group in groupby(meals, key=lambda x: x.timestamp.date()):
                date_str = date.isoformat()
                meals_list = list(group)
                
                logging.info(f"  Generating summary for {date_str} ({len(meals_list)} meals)...")
                
                try:
                    # Generate fresh summary
                    new_summary_text = ai_engine.generate_daily_summary(meals_list, user.daily_target)
                    
                    # 4. Upsert into daily_summaries table
                    existing = db.query(database.DailySummary).filter(
                        database.DailySummary.user_id == user.id,
                        database.DailySummary.date == date_str
                    ).first()
                    
                    if existing:
                        existing.content = new_summary_text
                    else:
                        new_summary = database.DailySummary(
                            user_id=user.id,
                            date=date_str,
                            content=new_summary_text
                        )
                        db.add(new_summary)
                    
                    db.commit()
                    logging.info(f"    ✓ Updated.")
                except Exception as e:
                    logging.error(f"    ✗ Failed for {date_str}: {e}")
                    db.rollback()

        logging.info("Backfill complete!")

    finally:
        db.close()

if __name__ == "__main__":
    backfill_summaries()
