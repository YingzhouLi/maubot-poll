import time

from maubot import Plugin
from maubot.handlers import command
from mautrix.types import MessageEvent, EventType

from .database import PollDatabase
from .types import Choice


def _remove_suffix(input_string, suffix):
    if suffix and input_string.endswith(suffix):
        return input_string[:-len(suffix)]
    return input_string


def _generate_poll_html_message(question: str, choices: list, code: str) -> str:
    message = f"<p><strong>Umfrage:</strong> <em>{question}</em></p>\n<ol>\n"
    for choice in choices:
        message = message + f"<li>{choice}</li>\n"
    message = message + f"\n</ol>\n<p><em>Stimme mit </em><code>!vote {code} &lt;Nummer&gt;</code><em> " \
                        "ab.</em></p>"
    return message


def _generate_poll_text_message(question: str, choices: list, code: str) -> str:
    message = f"Umfrage: {question}\n\n"
    for index, choice in enumerate(choices):
        message = message + f"{index}. {choice}\n"
    message = message + f"\nStimme mit !vote {code} <Nummer> ab."
    return message


def _generate_result_text_message(question: str, choices: list, total_votes: int) -> str:
    message = f"Umfrageergebnis: {question}\n"
    for choice in choices:
        message = message + f"{choice.number[0]}. {choice.content}\n    ({len(choice.votes)} von {total_votes} " \
                            f"Stimmen - {'{:.0%}'.format(len(choice.votes) / total_votes)})\n"
    return message


def _generate_result_html_message(question: str, choices: list, total_votes: int) -> str:
    message = f"<h4>Umfrageergebnis: <em>{question}</em></h4><ol>"
    for choice in choices:
        message = message + f"<li>{choice.content}<br><em>{len(choice.votes)} von {total_votes} " \
                            f"Stimmen - {'{:.0%}'.format(len(choice.votes) / total_votes)}</em></li>"
    return message + "</ol>"


class PollPlugin(Plugin):
    db: PollDatabase

    async def start(self) -> None:
        self.db = PollDatabase(self.database)

    async def _send_temporary_response(self, content: str, evt: MessageEvent, delay: int = 7):
        event = await evt.respond(content)
        time.sleep(delay)
        levels = await self.client.get_state_event(evt.room_id, EventType.ROOM_POWER_LEVELS)
        power_levels = await self.client.get_state_event(evt.room_id, EventType.ROOM_POWER_LEVELS)
        if levels.get_user_level(self.client.mxid) >= power_levels.redact:
            await self.client.redact(evt.room_id, evt.event_id)
        await self.client.redact(evt.room_id, event)

    def _sort_choices(self, poll_id: int):
        choices = self.db.get_poll_choices(poll_id)
        votes = self.db.get_votes(poll_id)

        total_votes = 0

        data = {}

        for choice in choices:
            data[choice.id] = Choice(choice.choice_number, choice.content)
        for vote in votes:
            total_votes = total_votes + 1
            data[vote.choice_id].votes.append(vote.voter)

        choices = list(data.values())
        choices.sort(key=lambda c: c.number)

        for choice in choices:
            choice.votes.sort()

        return total_votes, choices

    @command.new(name="poll", require_subcommand=True)
    async def poll_command(self, evt: MessageEvent):
        pass

    @poll_command.subcommand(name="create", aliases=["new"],
                             help="Erstelle eine neue Umfrage mit folgendem Format: "
                                  "`!poll create <Frage> | <Option 1> | <Option 2>`")
    @command.argument(name="content", label="Inhalt", pass_raw=True, required=True)
    async def create_poll(self, evt: MessageEvent, content: str):
        if content is not "":
            raw_parts = content.split("|")
            parts = []
            for part in raw_parts:
                parts.append(part.strip())
            if len(parts) < 3:
                evt.respond("Bitte gebe mindestens 2 Optionen an: `!poll create <Frage> | <Option 1> | <Option 2>`")
            else:
                question = parts[0]
                parts.pop(0)
                code = self.db.create_poll(question, parts, evt.sender, evt.room_id)
                await self.client.send_text(evt.room_id, _generate_poll_text_message(question, parts, code),
                                            _generate_poll_html_message(question, parts, code))
        else:
            await evt.respond(
                "Bitte gebe den Inhalt für die Umfrage an: `!poll create <Frage> | <Option 1> | <Option 2>`")

    @command.new(name="vote",
                 help="Nehme an einer Umfrage teil.")
    @command.argument(name="code", label="Code", pass_raw=False, required=True)
    @command.argument(name="choice", label="Möglichkeit", pass_raw=False, required=True)
    async def vote_poll(self, evt: MessageEvent, code: str, choice: str):
        poll = self.db.get_poll(evt.room_id, code)
        if poll.exists:
            choices = self.db.get_poll_choices_ids(poll.id)
            try:
                choice_id = choices[int(choice)]
                self.db.set_vote(poll.id, choice_id, evt.sender)
                await self._send_temporary_response(f"{evt.sender}, du hast für Option {choice} abgestimmt.", evt)
            except KeyError:
                await self._send_temporary_response("Diese Möglichkeit gibt es nicht!", evt)
            except ValueError:
                await self._send_temporary_response("Du musst eine gültige Möglichkeit angeben!", evt)
        else:
            await self._send_temporary_response("Diese Umfrage exsistiert nicht!", evt)

    @poll_command.subcommand("result", help="Zeigt dem Ersteller einer Umfrage das Ergebnis an.")
    @command.argument(name="code", label="Code", pass_raw=False, required=True)
    async def poll_result(self, evt: MessageEvent, code: str):
        poll = self.db.get_poll(evt.room_id, code)
        if not poll.exists:
            await self._send_temporary_response("Diese Umfrage exsistiert nicht!", evt)
            return

        if poll.creator.strip() != evt.sender.strip():
            await self._send_temporary_response("Nur der Ersteller einer Umfrage kann die Ergebnisse anzeigen lassen!",
                                                evt)
            return

        data = self._sort_choices(poll.id)
        total_votes = data[0]
        choices = data[1]

        await self.client.send_text(evt.room_id, _generate_result_text_message(poll.question, choices, total_votes),
                                    _generate_result_html_message(poll.question, choices, total_votes))

    @poll_command.subcommand("ping",
                             help="Pingt die Teilnehmer einer Umfrage an, die für die angegebene Möglichkeit gestimmt "
                                  "haben.")
    @command.argument(name="code", label="Code", pass_raw=False, required=True)
    @command.argument(name="option", label="Möglichkeit", pass_raw=False, required=True)
    async def ping_poll(self, evt: MessageEvent, code: str, option: str):
        poll = self.db.get_poll(evt.room_id, code)
        if not poll.exists:
            await self._send_temporary_response("Diese Umfrage exsistiert nicht!", evt)
            return

        if poll.creator.strip() != evt.sender.strip():
            await self._send_temporary_response("Nur der Ersteller einer Umfrage kann Teilnehmer anpingen!",
                                                evt)
            return

        try:
            opt = int(option)
            choices = self._sort_choices(poll.id)[1]
            for choice in choices:
                if choice.number[0] == opt:
                    msg = f"**Option {opt}:** *{choice.content}* \n\n"
                    for vote in choice.votes:
                        msg = msg + f"{vote}, "
                    await evt.respond(_remove_suffix(msg, ", "))
                    return
            raise ValueError
        except ValueError:
            await self._send_temporary_response("Du muss eine gültige Option angeben!", evt)
