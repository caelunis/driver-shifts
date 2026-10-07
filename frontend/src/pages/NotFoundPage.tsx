import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="narrow">
      <div className="panel">
        <h2>Страница не найдена</h2>
        <Link to="/">На главную</Link>
      </div>
    </div>
  );
}
