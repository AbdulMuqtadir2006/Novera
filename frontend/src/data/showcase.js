// Homepage "Behind Novera" showcase (2026-08-24) — team/paper/testing
// photos shown above the live workflow diagram. Empty by default: no real
// team/paper/testing photos exist in the project yet, and ImageSlideshow
// renders an honest "coming soon" placeholder for an empty array rather
// than a broken image or a stand-in stock photo.
//
// To add real photos: drop files into frontend/public/showcase/team/ and
// frontend/public/showcase/testing/ (any filenames), and list them below as
// { src: "/showcase/team/1.jpg", alt: "..." }. For the research paper, drop
// one image into frontend/public/showcase/ and set RESEARCH_PAPER.image.

export const TEAM_PHOTOS = [
  // { src: "/showcase/team/1.jpg", alt: "The Novera team at ..." },
];

export const TESTING_PHOTOS = [
  // { src: "/showcase/testing/1.jpg", alt: "Testing the Novera reader with ..." },
];

// Single static image, not a slideshow.
export const RESEARCH_PAPER = {
  image: null, // e.g. "/showcase/paper.jpg"
  link: null, // optional — e.g. a hosted PDF or DOI URL
};
