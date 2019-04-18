from datetime import datetime


class Message:
    def __init__(self,
                 date,
                 from_id,
                 id,
                 out,
                 peer_id,
                 text,
                 conversation_message_id,
                 fwd_messages,
                 important,
                 random_id,
                 attachments,
                 is_hidden):
        self.date = datetime.fromtimestamp(date)
        self.from_id = int(from_id)
        self.id = int(id)
        self.out = bool(out)
        self.peer_id = int(peer_id)
        self.text = text
        self.conversation_message_id = int(conversation_message_id)
        self.fwd_messages = fwd_messages
        self.important = bool(important)
        self.random_id = int(random_id)
        self.attachments = attachments
        self.is_hidden = bool(is_hidden)

    @staticmethod
    def to_python(obj):
        return Message(
            obj.get('date'),
            obj.get('from_id'),
            obj.get('id'),
            obj.get('out'),
            obj.get('peer_id'),
            obj.get('text'),
            obj.get('conversation_message_id'),
            obj.get('fwd_messages'),
            obj.get('important'),
            obj.get('random_id'),
            obj.get('attachments'),
            obj.get('is_hidden'),
        )

    def __str__(self):
        return f'[Message] From: {self.from_id} to: {self.peer_id}; text: {self.text}'
