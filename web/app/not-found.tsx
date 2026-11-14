import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-16 text-center">
      <h1 className="text-2xl font-semibold text-ink">This page does not exist</h1>
      <p className="mt-2 text-muted">The link may be out of date. Start again from the overview.</p>
      <Link href="/" className="mt-6 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink">
        Go to the overview
      </Link>
    </div>
  );
}
