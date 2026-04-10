module.exports = {
  content: ['./templates/**/*.html', './apps/**/templates/**/*.html', './static/js/**/*.js'],
  theme: {
    extend: {
      transitionProperty: {
        width: 'width',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(15, 23, 42, 0.06), 0 1px 1px rgba(15, 23, 42, 0.04)',
      },
    },
  },
  plugins: [],
};
