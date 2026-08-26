// Homepage "Meet the Team" section (2026-08-25). Drop portrait photos into
// frontend/public/team/ using the filenames below, and TeamMembersSection
// picks them up automatically — no other code change needed.

// Order is display order (Abdul in the middle, Hassan's call).
export const TEAM_MEMBERS = [
  {
    name: "Hamza Ait Azeroual",
    role: "Chemical Engineer | IoT Engineer",
    description:
      "Hamza is a Chemical Engineer with four years of technical experience. He leads the sensor development, testing and validation of Novera's product. His work focuses on making the sensors function accurately, carrying out technical testing, improving system performance and validating the measurements produced by the product.",
    photo: "/team/hamza.jpg",
  },
  {
    name: "Abdul Muqtadir Mohammed",
    role: "Computer Engineer | Technology & AI",
    description:
      "Abdul leads the technology and digital development of Novera. He developed the company's website and works across artificial intelligence, software development, system architecture and technical integration. His role focuses on connecting Novera's sensing technology with intelligent software and AI to build a complete, reliable and scalable health-tech product.",
    photo: "/team/abdul.jpg",
  },
  {
    name: "Hassan Ali Al Lawati",
    role: "Chemical Engineer | Business & Strategy",
    description:
      "Hassan leads the business and commercial direction of Novera. With a background in Chemical Engineering, he focuses on business development, market strategy, partnerships and commercialization. His role is to identify opportunities, build valuable relationships and help position Novera's technology as a strong and commercially viable health-tech product.",
    photo: "/team/hassan.jpg",
    // hassan.jpg is a much taller/narrower crop (720x1280) than the other two
    // photos, with a lot of empty background above his head — the default
    // object-top crop left excessive dead space above him and made his face
    // read small/distant compared to Hamza's and Abdul's tight headshot
    // crops. Shifted down (checked visually against a few offsets) so his
    // hat/face fill the frame the same way theirs do (2026-08-26).
    photoPosition: "center 45%",
  },
];
