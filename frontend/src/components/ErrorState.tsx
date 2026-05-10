export function ErrorState({ message }: { message: string }) {
  return (
    <div className="panel border-rose/40 bg-rose/5 p-5 text-sm text-rose">
      {message}
    </div>
  );
}
