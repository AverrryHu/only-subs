import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base, Channel, Video, User


class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.db")
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_channel(self, channel_id: str, channel_name: str, channel_url: str, custom_name: str = None) -> Channel:
        session = self.Session()
        try:
            channel = Channel(
                channel_id=channel_id,
                channel_name=channel_name,
                channel_url=channel_url,
                custom_name=custom_name
            )
            merged = session.merge(channel)
            session.commit()
            session.refresh(merged)
            return merged
        finally:
            session.close()

    def get_channels(self):
        session = self.Session()
        try:
            return session.query(Channel).all()
        finally:
            session.close()

    def get_channel_by_id(self, channel_id: int):
        session = self.Session()
        try:
            return session.query(Channel).filter(Channel.id == channel_id).first()
        finally:
            session.close()

    def get_channel_by_channel_id(self, channel_id: str):
        session = self.Session()
        try:
            return session.query(Channel).filter(Channel.channel_id == channel_id).first()
        finally:
            session.close()

    def add_video(self, video_id: str, channel_id: int, title: str, url: str,
                thumbnail: str = None, published_at=None, duration: int = None) -> Video:
        session = self.Session()
        try:
            existing = session.query(Video).filter(Video.video_id == video_id).first()
            if existing:
                return None
            video = Video(
                video_id=video_id,
                channel_id=channel_id,
                title=title,
                url=url,
                thumbnail=thumbnail,
                published_at=published_at,
                duration=duration,
                has_new=True
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            return video
        finally:
            session.close()

    def get_videos(self, channel_id: int = None, has_new: bool = None):
        session = self.Session()
        try:
            query = session.query(Video)
            if channel_id:
                query = query.filter(Video.channel_id == channel_id)
            if has_new is not None:
                query = query.filter(Video.has_new == has_new)
            return query.order_by(Video.published_at.desc()).all()
        finally:
            session.close()

    def get_video(self, video_id: str):
        session = self.Session()
        try:
            return session.query(Video).filter(Video.video_id == video_id).first()
        finally:
            session.close()

    def update_subtitles(self, video_id: str, subtitles: str):
        session = self.Session()
        try:
            video = session.query(Video).filter(Video.video_id == video_id).first()
            if video:
                video.subtitles = subtitles
                session.commit()
        finally:
            session.close()

    def mark_as_read(self, video_id: str):
        session = self.Session()
        try:
            video = session.query(Video).filter(Video.video_id == video_id).first()
            if video:
                video.has_new = False
                session.commit()
        finally:
            session.close()

    def delete_channel(self, channel_id: int):
        session = self.Session()
        try:
            channel = session.query(Channel).filter(Channel.id == channel_id).first()
            if channel:
                # 先删除该频道的所有视频
                session.query(Video).filter(Video.channel_id == channel_id).delete()
                # 再删除频道
                session.delete(channel)
                session.commit()
        finally:
            session.close()

    def delete_video(self, video_id: int):
        session = self.Session()
        try:
            video = session.query(Video).filter(Video.id == video_id).first()
            if video:
                session.delete(video)
                session.commit()
        finally:
            session.close()

    def get_user(self):
        session = self.Session()
        try:
            return session.query(User).first()
        finally:
            session.close()

    def save_user(self, sessdata: str, bili_jct: str = None, buvid3: str = None):
        session = self.Session()
        try:
            user = session.query(User).first()
            if user:
                user.sessdata = sessdata
                user.bili_jct = bili_jct
                user.buvid3 = buvid3
            else:
                user = User(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)
                session.add(user)
            session.commit()
        finally:
            session.close()