// Homepage "Behind Novera" showcase (2026-08-24) — team/paper/testing
// photos shown above the live workflow diagram. ImageSlideshow renders an
// honest "coming soon" placeholder for an empty array rather than a broken
// image or a stand-in stock photo — real files added 2026-08-25.
//
// To add more photos: drop files into frontend/public/showcase/team/ or
// frontend/public/showcase/testing/, and list them below as
// { src: "/showcase/team/whatever.jpg", alt: "..." }. For the research
// paper, drop one image into frontend/public/showcase/ and set
// RESEARCH_PAPER.image.

export const TEAM_PHOTOS = [
  { src: "/showcase/team/team-1.jpg", alt: "The Novera team" },
  { src: "/showcase/team/team-2.jpg", alt: "The Novera team" },
  { src: "/showcase/team/team-3.jpg", alt: "The Novera team" },
  { src: "/showcase/team/team-4.jpg", alt: "The Novera team" },
];

export const TESTING_PHOTOS = [
  { src: "/showcase/testing/testing-1.jpg", alt: "Testing the Novera device" },
];

// Single static image, not a slideshow.
export const RESEARCH_PAPER = {
  image: "/showcase/paper.jpg",
  link: null, // optional — e.g. a hosted PDF or DOI URL
};
