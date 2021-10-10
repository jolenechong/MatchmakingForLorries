from website import create_app, db

app = create_app()

import pytz
import datetime
from datetime import timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from website.models import Request, Notification


def reminder():
    with app.app_context():
        all_requests = Request.query.filter_by(status='Finding match')

    current_time = str(datetime.datetime.today())
    datetime_str = current_time[5:7] + '/' + current_time[8:10] + '/' + current_time[2:4] + ' ' + current_time[11:-7]
    current_time = datetime.datetime.strptime(datetime_str, '%m/%d/%y %H:%M:%S')
    
    for req in all_requests:
        close = req.closing_time
        if (close - timedelta(hours=2)) > close > current_time:
            # 2hrs before closing will run this but nt yet current time
            # since code runs every hour means they will at least get 1 or 2 notifications

            notif = Notification(user_id=req.user_id,request_status='Closing time is near!', request_id=req.id)
            with app.app_context():
                db.session.add(notif)
                db.session.commit()


scheduler = BackgroundScheduler()
scheduler.configure(timezone=pytz.timezone('UTC'))
scheduler.add_job(func=reminder, trigger="interval", seconds=30)
# run this code every hour
scheduler.start()


if __name__ == '__main__':
    app.run(debug=True)

    