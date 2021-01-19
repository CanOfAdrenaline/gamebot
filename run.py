import os
import logging

from core import Bot
from games import Chess, Resistance

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def main():
    bot = Bot(token=os.environ['GAMEBOT_TELEGRAM_TOKEN'])
    bot.game_manager.add_game('chess', Chess)
    bot.game_manager.add_game('resistance', Resistance)
    bot.run()
    
    
if __name__ == '__main__':
    main()
