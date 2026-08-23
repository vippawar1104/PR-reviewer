import datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(primary_key=True)  # GitHub installation_id, not autoincrement
    account_login: Mapped[str]
    installed_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    reviews: Mapped[list["Review"]] = relationship(back_populates="installation")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("repo_full_name", "pr_number", "commit_sha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_id: Mapped[int] = mapped_column(ForeignKey("installations.id"))
    repo_full_name: Mapped[str]
    pr_number: Mapped[int]
    commit_sha: Mapped[str]
    summary: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    installation: Mapped["Installation"] = relationship(back_populates="reviews")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"))
    file: Mapped[str]
    line: Mapped[int]
    severity: Mapped[str]
    category: Mapped[str]
    comment: Mapped[str]
    posted: Mapped[bool] = mapped_column(default=False)

    review: Mapped["Review"] = relationship(back_populates="findings")
