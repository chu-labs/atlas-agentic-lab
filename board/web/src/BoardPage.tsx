import { Link } from "react-router-dom";
import { usePoll } from "./api";
import { Avatar } from "./Avatar";
import { slug } from "./App";
import { TYPE_GLYPH, type Board, type Card } from "./types";
import { shortDate } from "./time";

export default function BoardPage() {
  const { data, error } = usePoll<Board>("/api/board?sprint=active", 2000);
  if (!data) return <main className="page center muted">{error ? `Cannot reach the board: ${error}` : "Loading…"}</main>;
  const sp = data.sprint;
  return (
    <main className="page board-page">
      {sp && (
        <section className="sprint">
          <div>
            <h1 className="sprint-name">{sp.name}</h1>
            <p className="sprint-goal">{sp.goal}</p>
          </div>
          <div className="sprint-dates">
            {shortDate(sp.starts_on)} → {shortDate(sp.ends_on)}
          </div>
        </section>
      )}
      <section className="columns">
        {data.columns.map((col) => (
          <div key={col.status} className={`column column-${slug(col.status)}`}>
            <h2 className="column-title">
              <span>{col.status}</span>
              <span className="column-count">{col.issues.length}</span>
            </h2>
            <div className="cards">
              {col.issues.map((c) => (
                <IssueCard key={c.key} card={c} />
              ))}
            </div>
          </div>
        ))}
      </section>
    </main>
  );
}

function IssueCard({ card }: { card: Card }) {
  return (
    <Link to={`/issue/${card.key}`} className={`card type-${card.type.toLowerCase()}`}>
      <div className="card-top">
        <span className="type-glyph" title={card.type}>
          {TYPE_GLYPH[card.type]}
        </span>
        <span className="card-key">{card.key}</span>
        {card.pr_url && <span className="pr-dot" title="has a pull request">PR</span>}
      </div>
      <div className="card-title">{card.title}</div>
      <div className="card-bottom">
        <span className={`chip prio prio-${card.priority.toLowerCase()}`}>{card.priority}</span>
        {card.story_points != null && <span className="chip points">{card.story_points}</span>}
        <span className="spacer" />
        <Avatar user={card.assignee} size={40} />
      </div>
    </Link>
  );
}
