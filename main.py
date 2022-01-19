import logging
import re
import os
import datetime
import random

import peewee

from functools import partial

from telegram import Update, ForceReply
from telegram.utils.helpers import escape_markdown
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)


VALID_GAMES = [
    ("Wordle", r"^Wordle (?P<run>\d+) (?P<score>X|\d+)/6\*?\n"),
    ("Woordle", r"^Woordle (?P<run>\d+) (?P<score>X|\d+)/6\n"),
    ("Woordle6", r"^Woordle6 (?P<run>\d+) (?P<score>X|\d+)/6\n"),
]


REACTIONS = [
    (
        6,
        6,
        "Are you cheating, {player}? That's worth {score} points for {game} {run}\!",
    ),
    (
        6,
        6,
        "Clearly, {player} is clairvoyant\. They get {score} whole points for {game} {run}\!",
    ),
    (
        4,
        5,
        "Great work, {player}\! You get {score} points for {game} {run}\.",
    ),
    (
        4,
        5,
        "Wow, {player} is unstoppable\. They get {score} points for {game} {run}\!",
    ),
    (
        2,
        5,
        "For {game} {run}, we're awarding {score} points to {player}\!",
    ),
    (
        2,
        5,
        "Well done, {player}\. That's worth {score} points for {game} {run}\.",
    ),
    (
        0,
        1,
        "Not your best work, {player}\. Here's {score} point for {game} {run}\.",
    ),
    (
        0,
        2,
        "Better luck next time, {player}\. You get {score} points for {game} {run}\.",
    ),
    (
        0,
        100000,
        "Awarding {score} points to {player} for {game} {run}\.",
    ),
]


DB = peewee.SqliteDatabase(os.getenv("TELEGRAM_DATABASE", "wordlegram.db"))


class Score(peewee.Model):
    time = peewee.DateTimeField(default=datetime.datetime.now)
    game = peewee.FixedCharField(max_length=16)
    run = peewee.IntegerField()
    player = peewee.IntegerField()
    score = peewee.IntegerField()
    chat = peewee.IntegerField()

    class Meta:
        primary_key = peewee.CompositeKey("game", "run", "player", "chat")
        database = DB


def select_reaction(score):
    return random.choice(
        [reaction for lo, hi, reaction in REACTIONS if lo <= score and hi >= score]
    )


def score(update: Update, context: CallbackContext) -> None:
    scores = (
        Score.select(Score.player, peewee.fn.SUM(Score.score).alias("total"))
        .where(Score.chat == update.message.chat.id)
        .group_by(Score.player)
    )

    items = sorted([i for i in scores], key=lambda x: x.total, reverse=True)

    message = "Here's the current scoreboard for this channel:\n\n"

    for n, i in enumerate(items):
        user = context.bot.get_chat_member(update.message.chat.id, i.player)
        message += "{n}\. [{player_first_name} {player_last_name}](tg://user?id={player_id}) \({score} points\)\n".format(
            n=n + 1,
            player_first_name=user.user.first_name,
            player_last_name=user.user.last_name,
            player_id=i.player,
            score=i.total,
        )

    update.message.reply_markdown_v2(message)


def echo(update: Update, context: CallbackContext) -> None:
    for name, pattern in VALID_GAMES:
        if m := re.match(pattern, update.message.text):
            try:
                score = max(0, min(6, 7 - int(m.group("score"))))
            except ValueError:
                score = 0

            run = int(m.group("run"))

            try:
                Score.create(
                    game=name,
                    run=run,
                    player=update.message.from_user.id,
                    score=score,
                    chat=update.message.chat.id,
                )

                reaction = select_reaction(score)

                update.message.reply_markdown_v2(
                    reaction.format(
                        player=update.message.from_user.first_name,
                        score=score,
                        game=name,
                        run=run,
                    )
                )
            except peewee.IntegrityError:
                update.message.reply_markdown_v2(
                    "Sorry, but you've already submitted a score for {game} {run}\.".format(
                        game=name, run=run
                    )
                )

            break


def main() -> None:
    DB.connect()

    DB.create_tables([Score])

    updater = Updater(os.getenv("TELEGRAM_BOT_TOKEN"))

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("score", score))
    dispatcher.add_handler(
        MessageHandler(Filters.text & ~Filters.command & Filters.chat_type.groups, echo)
    )

    updater.start_polling()

    updater.idle()

    DB.close()


if __name__ == "__main__":
    main()
