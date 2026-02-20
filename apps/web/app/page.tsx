import Link from "next/link";

export default function HomePage() {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "100vh",
      gap: "2rem"
    }}>
      <h1>Welcome to Overplanned</h1>
      <p>Behavioral-driven travel planning</p>
      <Link href="/auth/signin">
        <button
          style={{
            padding: "12px 24px",
            fontSize: "16px",
            cursor: "pointer",
            backgroundColor: "#4285f4",
            color: "white",
            border: "none",
            borderRadius: "4px",
          }}
        >
          Get Started
        </button>
      </Link>
    </div>
  );
}
