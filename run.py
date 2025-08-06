from app import app 
import logging
from logging.handlers import RotatingFileHandler
import os

if __name__== '__main__':
    app.run(debug=True)




if not os.path.exists('logs'):
    os.mkdir('logs')

file_handler = RotatingFileHandler('logs/houda_app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Application Houda démarrée')
