from . import create_flask, create_dash, db_startup
from .layouts import main_layout_header, main_layout_sidebar
from apscheduler.schedulers.background import BackgroundScheduler

# The Flask instance
server = create_flask()

# The Dash instance
app = create_dash(server)

# New DB startup tasks
db_startup(app)

# Logging
import logging
from logging.handlers import RotatingFileHandler
from .utils import config
from .api.sqlalchemy_declarative import dbRefreshStatus

# Can also use %(pathname)s for full pathname for file instead of %(module)s
handler = RotatingFileHandler('./config/log.log', maxBytes=10000000, backupCount=5)
formatter = logging.Formatter("[%(asctime)s] %(levelname)s from %(module)s line %(lineno)d - %(message)s")
handler.setFormatter(formatter)
app.server.logger.setLevel(config.get('logger', 'level'))
app.server.logger.addHandler(handler)
# Suppress WSGI info logs
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Push an application context so we can use Flask's 'current_app'
with server.app_context():
    # load the rest of our Dash app
    from . import index

    # Enable refresh cron
    if config.get('cron', 'hourly_pull').lower() == 'true':
        try:
            from .api.datapull import refresh_database

            scheduler = BackgroundScheduler()
            scheduler.add_job(func=refresh_database, trigger="cron", hour='*')
            app.server.logger.info('Starting cron jobs')
            scheduler.start()
        except BaseException as e:
            app.server.logger.error(f'Error starting cron jobs: {e}')

    # Delete any audit logs for running processes, since restarting server would stop any processes
    app.session.query(dbRefreshStatus).filter(dbRefreshStatus.refresh_method == 'processing').delete()
    app.session.commit()
    app.session.remove()
    # configure the Dash instance's layout
    app.layout = main_layout_header()
    # app.layout = main_layout_sidebar()


